"""Accepted Scott Living literals, real HA callers and original-link cancellation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds import scott_living as bed
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import scott_living as profiles
from tests.hold_lease_wire import virtual_clock
from tests.test_somos import gatt, written

FIXTURES = Path(__file__).parent / "fixtures/scott_living"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
CONTROLS = json.loads((FIXTURES / "controls.json").read_text())
ADDRESS = "AA:BB:CC:DD:00:54"


def entry(hass, layout):
    e = MockConfigEntry(
        domain=const.DOMAIN,
        title="Scott Living",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Scott Living",
            const.CONF_BED_TYPE: "scott_living",
            const.CONF_PRODUCT_TYPE: layout,
            const.CONF_BLE_DEVICE_NAME: "base00000000",
            const.CONF_MOTOR_COUNT: 3 if layout == "C" else 2,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    e.add_to_hass(hass)
    return e


async def connected(hass, client, layout="C"):
    c = AdjustableBedCoordinator(hass, entry(hass, layout))
    c._client = client
    c._controller = controller = bed.ScottLivingController(
        c, layout=layout, device_name="base00000000"
    )
    client.services = gatt("a")
    with virtual_clock():
        await controller.start_notify()
    client.write_gatt_char.reset_mock()
    return c, controller


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_all_frozen_literals(vector):
    inputs = vector["inputs"]
    expected = bytes.fromhex(vector["expected_bytes"])
    if "key" in inputs:
        assert codec.frame(inputs["key"] & 0xFFFFFFFF, header=0xE6, side=1) == expected
    elif "name" in inputs:
        assert codec.scott_living_query(inputs["name"]) == expected
    else:
        indicator = vector["expected_parse"]["indicator"]
        assert codec.scott_living_timer_indicator(expected) == (
            None if indicator == "unchanged" else 0 if indicator == "all normal" else int(indicator)
        )


def test_query_name_and_parser_fail_closed():
    with pytest.raises(ValueError):
        codec.scott_living_query("baseNOTHEX!!")
    assert codec.scott_living_query("long-prefix-00000000") == codec.scott_living_query(
        "base00000000"
    )
    assert codec.scott_living_query("short") == codec.scott_living_query(None)
    for length in range(16):
        assert codec.scott_living_timer_indicator(bytes(length)) is None
    assert codec.scott_living_timer_indicator(bytes(16)) is None


@pytest.mark.parametrize("layout", profiles.LAYOUTS)
async def test_manual_setup_and_owned_layout(hass, layout):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.setup_questions import setup_profile
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["scott_living"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: layout})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == (3 if layout == "C" else 2)
    assert saved[const.CONF_PRODUCT_TYPE] == layout
    declaration = setup_profile("scott_living")
    assert declaration is not None and declaration.validate is not None
    assert declaration.validate({**saved, const.CONF_PRODUCT_TYPE: "D"})
    assert declaration.validate(saved) == {}


@pytest.mark.parametrize("layout", profiles.LAYOUTS)
async def test_every_control_through_real_ha_entities(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    layout,
    mock_async_ble_device_from_address,
):
    mock_bleak_client.services = gatt("a")
    mock_async_ble_device_from_address.return_value.name = "base00000000"
    e = entry(hass, layout)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[const.DOMAIN][e.entry_id]
    controller = coordinator.controller
    assert isinstance(controller, bed.ScottLivingController)
    assert len(controller.profile.actions) == {"A": 8, "B": 13, "C": 17}[layout]
    assert not controller.supports_single_address_pairing
    assert controller.memory_slot_count == 0
    registry = er.async_get(hass)
    entities = [v for v in registry.entities.values() if v.config_entry_id == e.entry_id]
    assert not any("lumbar" in v.unique_id or "memory_" in v.unique_id for v in entities)
    device = next(v.device_id for v in entities if v.device_id)
    # Raw M/star controls use the standard utility shape, disabled until chosen.
    for item in entities:
        if item.unique_id.endswith(("m_button", "star_button")):
            registry.async_update_entity(item.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[const.DOMAIN][e.entry_id].controller
    with virtual_clock():
        await controller.start_notify()
        for row in (r for r in CONTROLS if r.get("variant") == layout and "key" in r):
            action = next(a for a in controller.profile.actions if a.mask == row["key"])
            mock_bleak_client.write_gatt_char.reset_mock()
            if action.mode == "held":
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": device, "control": action.key, "duration": 0.1},
                    blocking=True,
                )
            else:
                suffix = "preset_flat" if action.key == "flat" else action.key
                target = next(
                    v.entity_id
                    for v in registry.entities.values()
                    if v.config_entry_id == e.entry_id and v.unique_id.endswith(suffix)
                )
                await hass.services.async_call(
                    "button", "press", {"entity_id": target}, blocking=True
                )
            assert written(mock_bleak_client) == [bytes.fromhex(row["bytes"]).hex()], row
    current = hass.data[const.DOMAIN][e.entry_id]
    current.async_ensure_connected = AsyncMock(side_effect=AssertionError("STOP reconnected"))
    current._client = None
    mock_bleak_client.write_gatt_char.reset_mock()
    cover = next(
        v.entity_id
        for v in registry.entities.values()
        if v.config_entry_id == e.entry_id and v.domain == "cover"
    )
    await hass.services.async_call("cover", "stop_cover", {"entity_id": cover}, blocking=True)
    current.async_ensure_connected.assert_not_awaited()
    mock_bleak_client.write_gatt_char.assert_not_called()
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("layout", profiles.LAYOUTS)
async def test_exact_refresh_and_no_release(hass, mock_bleak_client, layout):
    _, controller = await connected(hass, mock_bleak_client, layout)
    with virtual_clock() as clock:
        writes = []

        async def record(*args, **kwargs):
            writes.append(round(clock.now * 1000))

        mock_bleak_client.write_gatt_char.side_effect = record
        await controller.hold_control("head_up", 250)
        assert writes == [0, 100, 200]
    assert written(mock_bleak_client) == ["e6fe16010000000103"] * 3
    await controller.stop_all()
    assert len(written(mock_bleak_client)) == 3


@pytest.mark.parametrize("cause", ("stop", "cancel", "reconnect", "deadline"))
async def test_queued_first_write_is_fenced(hass, mock_bleak_client, cause):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    coordinator, controller = await connected(hass, mock_bleak_client)
    await controller.ble_lock.acquire()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=coordinator.cancel_command,
        admitted_stop_epoch=0,
        intent_id="queued",
        kind=CommandKind.HOLD,
        group_id=None,
        resources=frozenset({"motor:*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    task = asyncio.create_task(controller.hold_control("head_up", 250))
    _CURRENT_COMMAND_CONTEXT.reset(token)
    for _ in range(8):
        await asyncio.sleep(0)
    stop = None
    if cause == "stop":
        stop = asyncio.create_task(controller.stop_all())
        await asyncio.sleep(0)
    elif cause == "cancel":
        coordinator.cancel_command.set()
    elif cause == "reconnect":
        coordinator._client = AsyncMock(is_connected=True)
    else:
        context.hold_deadline = asyncio.get_running_loop().time() - 1
    controller.ble_lock.release()
    try:
        await task
    except ConnectionError, asyncio.CancelledError:
        pass
    if stop is not None:
        await stop
    mock_bleak_client.write_gatt_char.assert_not_called()


async def test_public_stop_settles_inflight_write_without_reconnect(hass, mock_bleak_client):
    coordinator, controller = await connected(hass, mock_bleak_client)
    submitted, finish = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        submitted.set()
        await finish.wait()

    mock_bleak_client.write_gatt_char.side_effect = slow
    coordinator.async_ensure_connected = AsyncMock(return_value=True)
    task = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda c: c.hold_control("head_up", 1000))
    )
    await submitted.wait()
    coordinator.async_ensure_connected.reset_mock()
    stop = asyncio.create_task(coordinator.async_stop_command())
    for _ in range(8):
        await asyncio.sleep(0)
    assert not stop.done()
    replacement = AsyncMock(is_connected=True)
    coordinator._client = replacement
    finish.set()
    await asyncio.gather(task, stop, return_exceptions=True)
    assert stop.exception() is None
    assert written(mock_bleak_client) == ["e6fe16010000000103"]
    replacement.write_gatt_char.assert_not_called()
    coordinator.async_ensure_connected.assert_not_awaited()
    await coordinator.async_stop_command()
    coordinator.async_ensure_connected.assert_not_awaited()


async def test_stale_notifications_do_not_publish_and_timer_is_not_optimistic(
    hass, mock_bleak_client
):
    coordinator, controller = await connected(hass, mock_bleak_client)
    sender, receive = mock_bleak_client.start_notify.call_args.args
    packet = bytearray.fromhex(VECTORS[-4]["expected_bytes"])
    receive(sender, packet)
    assert coordinator.controller_state[bed.TIMER_INDICATOR] == 10
    await controller._run_action("massage_timer")
    assert coordinator.controller_state[bed.TIMER_INDICATOR] == 10
    coordinator._client = AsyncMock(is_connected=True)
    receive(sender, bytearray.fromhex(VECTORS[-2]["expected_bytes"]))
    assert coordinator.controller_state[bed.TIMER_INDICATOR] == 10
    controller.on_disconnect()
    assert coordinator.controller_state[bed.TIMER_INDICATOR] is None
    receive(sender, packet)
    assert coordinator.controller_state[bed.TIMER_INDICATOR] is None


@pytest.mark.parametrize("bad", ("service", "write", "notify"))
async def test_same_gatt_gate_for_setup_and_runtime(hass, mock_bleak_client, bad):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    coordinator, controller = await connected(hass, mock_bleak_client)
    controller.on_disconnect()
    mock_bleak_client.start_notify.reset_mock()
    if bad == "service":
        mock_bleak_client.services[0].uuid = "wrong"
    else:
        mock_bleak_client.services[0 if bad == "write" else 1].characteristics[0].properties = [
            "read"
        ]
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    with pytest.raises(ConnectionError):
        flow._migration_endpoint_check(mock_bleak_client, coordinator.entry.data)
    with pytest.raises(ConnectionError):
        await controller.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await controller.start_notify()
    mock_bleak_client.start_notify.assert_not_called()
    mock_bleak_client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("valid", (True, False))
async def test_setup_probe_requires_exact_roles_without_writing(
    hass, monkeypatch, mock_bleak_client, valid
):
    from custom_components.adjustable_bed import config_flow
    from tests.test_config_flow import _fresh_gate

    mock_bleak_client.services = gatt("a")
    if not valid:
        mock_bleak_client.services[0].characteristics[0].properties = ["read"]
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    freshness, device = _fresh_gate("hci0", -55)
    monkeypatch.setattr(config_flow, "async_gate_connection", lambda *a, **kw: (freshness, device))
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=mock_bleak_client)
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    info = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", info)
    report = await flow._probe_capabilities(ADDRESS, "auto", "scott_living", "auto")
    assert report.scott_living_transport_valid is valid
    assert bool(report.error) is not valid
    info.assert_not_awaited()
    mock_bleak_client.write_gatt_char.assert_not_called()
    mock_bleak_client.disconnect.assert_awaited_once()


async def test_failed_setup_gate_cannot_be_overridden(hass):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        CapabilityReport,
    )
    from custom_components.adjustable_bed.setup_operation import OperationOutcome, OperationResult

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._pending_entry = {"address": ADDRESS, "bed_type": "scott_living", "product_type": "C"}
    flow._pending_title = "Scott Living"
    flow.operation.result = OperationResult(
        outcome=OperationOutcome.CONNECTION_FAILED,
        payload=CapabilityReport(connected=False, scott_living_transport_valid=False),
    )
    create = flow._async_create_selected_app_entry = AsyncMock()
    assert (await flow.async_step_verify_connection())["step_id"] == "verify_connection"
    assert (await flow.async_step_verify_connection({"action": "finish"}))[
        "step_id"
    ] == "verify_connection"
    create.assert_not_awaited()


async def test_late_subscribe_cannot_query_or_clear_replacement_session(hass, mock_bleak_client):
    coordinator, controller = await connected(hass, mock_bleak_client)
    controller.on_disconnect()
    started, finish = asyncio.Event(), asyncio.Event()

    async def subscribe(*args, **kwargs):
        started.set()
        await finish.wait()

    mock_bleak_client.start_notify.side_effect = subscribe
    old = asyncio.create_task(controller.start_notify())
    await started.wait()
    controller.on_disconnect()
    replacement = AsyncMock(is_connected=True)
    replacement.services = gatt("a")
    coordinator._client = replacement
    # The original subscription still owns the lane until it settles.
    new = asyncio.create_task(controller.start_notify())
    finish.set()
    await asyncio.gather(old, new, return_exceptions=True)
    assert controller._session_client is replacement
    mock_bleak_client.write_gatt_char.assert_not_called()
    assert [bytes(c.args[1]) for c in replacement.write_gatt_char.call_args_list] == [
        codec.scott_living_query("base00000000")
    ]


@pytest.mark.parametrize("ending", ("stop", "expire"))
async def test_renewable_public_hold_ends_without_release(ending):
    from tests.hold_lease_wire import leased_hold

    result = await leased_hold(
        "scott_living:C", lambda c: c.hold_control("tilt_up", 100), end_after_s=0.35, end=ending
    )
    assert [write.at_ms for write in result.held] == [0, 100, 200, 300]
    assert {write.data.hex() for write in result.held} == {"e6fe161000000001f4"}
    assert result.after == ()
