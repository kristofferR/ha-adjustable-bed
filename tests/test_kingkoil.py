"""King Koil's accepted frames through real app setup, HA entities and holds."""

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
from custom_components.adjustable_bed.beds.keeson import kingkoil as bed
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.profiles import kingkoil as app
from tests.hold_lease_wire import virtual_clock
from tests.test_somos import gatt, written

VECTORS = json.loads((Path(__file__).parent / "fixtures/kingkoil/vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:27"


def entry(hass, selector):
    from custom_components.adjustable_bed.setup_questions import _kingkoil_settings

    e = MockConfigEntry(
        domain=const.DOMAIN,
        title="King Koil",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "King Koil",
            const.CONF_BED_TYPE: "kingkoil",
            const.CONF_PROTOCOL_VARIANT: selector,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
            **_kingkoil_settings({const.CONF_PROTOCOL_VARIANT: selector}),
        },
    )
    e.add_to_hass(hass)
    return e


@pytest.mark.parametrize(
    "row", [r for r in VECTORS if r["id"].startswith("N")], ids=lambda r: r["id"]
)
def test_frozen_parser_boundaries(row):
    parsed = codec.parse_kingkoil_status(bytes.fromhex(row["inputs"]["notification_hex"]))
    assert parsed is not None
    assert {"light": parsed.light, "timer_ui": parsed.timer_ui} == row["expected_parse"]
    for length in range(13):
        assert codec.parse_kingkoil_status(bytes(length)) is None


@pytest.mark.parametrize("selector", app.LAYOUTS)
async def test_manual_app_ingress_and_restore(hass, selector):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["kingkoil"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: selector})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    layout = app.LAYOUTS[selector]
    assert saved[const.CONF_MOTOR_COUNT] == len(layout.axes)
    assert saved[const.CONF_HAS_MASSAGE] == layout.massage
    assert resolve_profile_id(saved) == f"kingkoil:{selector}"
    assert per_side_profile("kingkoil", selector).variant_owned


@pytest.mark.parametrize("selector", app.LAYOUTS)
async def test_every_action_has_real_ha_ingress(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, selector
):
    mock_bleak_client.services = gatt("b")
    e = entry(hass, selector)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[const.DOMAIN][e.entry_id]
    controller = coordinator.controller
    assert isinstance(controller, bed.KingKoilController)
    registry = er.async_get(hass)
    entities = {
        item.unique_id: item
        for item in registry.entities.values()
        if item.config_entry_id == e.entry_id
    }
    device = next(iter(entities.values())).device_id
    layout = app.LAYOUTS[selector]
    assert set(controller.held_control_options) == {
        *(f"{axis}_{d}" for axis, _, _ in layout.axes for d in ("up", "down")),
        *(("light",) if selector == "KSBT03CK" else ()),
    }
    assert not controller.supports_single_address_pairing
    assert not controller.supports_memory_programming
    assert controller.memory_slot_count == 0
    query = next(
        item for item in entities.values() if item.unique_id.endswith("kingkoil_status_query")
    )
    assert query.disabled_by is not None
    registry.async_update_entity(query.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    with virtual_clock():
        # Exercise every vector's corresponding public ingress, rather than
        # checking a byte table without proving that a caller can reach it.
        for row in (r for r in VECTORS if r.get("variant") == selector):
            mock_bleak_client.write_gatt_char.reset_mock()
            raw = row["action"]
            if raw.endswith(("up", "down", "up (source label)", "down (source label)")):
                control = (
                    raw.removesuffix(" (source label)")
                    .lower()
                    .replace("foot", "feet")
                    .replace(" ", "_")
                )
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {
                        "device_id": device,
                        "control": control,
                        "duration": 0.1,
                    },
                    blocking=True,
                )
            else:
                action = {
                    "zero gravity": "zero_g",
                    "TV preset": "tv",
                    "flat preset": "flat",
                    "poll status": "status_query",
                    "light button (transition unspecified)": "light",
                    "massage mode (cycle unspecified)": "massage_mode",
                    "head massage (level/on-off unspecified)": "massage_head",
                    "foot massage (level/on-off unspecified)": "massage_foot",
                    "massage timer (cycle unspecified)": "massage_timer",
                }[raw]
                suffix = (
                    f"kingkoil_{action}"
                    if action in (*layout.actions, "status_query")
                    else f"preset_{action}"
                )
                target = next(
                    item.entity_id
                    for item in registry.entities.values()
                    if item.config_entry_id == e.entry_id and item.unique_id.endswith(suffix)
                )
                await hass.services.async_call(
                    "button", "press", {"entity_id": target}, blocking=True
                )
            assert written(mock_bleak_client) == [bytes.fromhex(row["expected_bytes"]).hex()], row[
                "id"
            ]
    assert await hass.config_entries.async_unload(e.entry_id)


async def connected(hass, client, selector="KSBT03CK"):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    e = entry(hass, selector)
    c = AdjustableBedCoordinator(hass, e)
    c._client = client
    c._controller = controller = bed.KingKoilController(c, variant=selector)
    client.services = gatt("b")
    await controller.async_discover_capabilities()
    return c, controller


@pytest.mark.parametrize("cause", ["stop", "cancel", "reconnect", "deadline"])
async def test_pending_first_write_is_fenced(hass, mock_bleak_client, cause):
    coordinator, controller = await connected(hass, mock_bleak_client)
    with virtual_clock():
        await controller._ble_lock.acquire()
        task = asyncio.create_task(controller.hold_control("head_up", 100))
        for _ in range(8):
            await asyncio.sleep(0)
        if cause == "stop":
            await controller.stop_all()
        elif cause == "cancel":
            coordinator.cancel_command.set()
        elif cause == "reconnect":
            coordinator._client = AsyncMock(is_connected=True)
        else:
            await asyncio.sleep(0.12)
        controller._ble_lock.release()
        try:
            await task
        except asyncio.CancelledError, ConnectionError:
            pass
        assert written(mock_bleak_client) == []


async def test_submitted_write_settles_before_cancel_and_no_replacement_movement(
    hass, mock_bleak_client
):
    coordinator, controller = await connected(hass, mock_bleak_client)
    started, finish = asyncio.Event(), asyncio.Event()

    async def slow_write(*args, **kwargs):
        started.set()
        await finish.wait()

    mock_bleak_client.write_gatt_char.side_effect = slow_write
    task = asyncio.create_task(controller.hold_control("head_up", 900))
    await started.wait()
    task.cancel()
    await controller.stop_all()
    replacement = AsyncMock(is_connected=True)
    coordinator._client = replacement
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    try:
        await task
    except asyncio.CancelledError, ConnectionError:
        pass
    assert written(mock_bleak_client) == ["040200000001"]
    replacement.write_gatt_char.assert_not_called()
    await controller.stop_all()
    replacement.write_gatt_char.assert_not_called()


async def test_reported_state_is_current_link_only(hass, mock_bleak_client):
    coordinator, controller = await connected(hass, mock_bleak_client)
    await controller.start_notify()
    sender, callback = mock_bleak_client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("00000002590000000000000001"))
    assert coordinator.controller_state[bed.LIGHT_REPORT] is True
    assert coordinator.controller_state[bed.TIMER_UI] == 20
    await controller.perform_action("massage_timer")
    assert coordinator.controller_state[bed.TIMER_UI] == 20
    controller.on_disconnect()
    callback(sender, bytearray(13))
    assert coordinator.controller_state[bed.LIGHT_REPORT] is None
    assert coordinator.controller_state[bed.TIMER_UI] is None


@pytest.mark.parametrize("malformation", ["service", "write", "notify"])
async def test_gatt_roles_rejected_by_setup_and_runtime(hass, mock_bleak_client, malformation):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    _, controller = await connected(hass, mock_bleak_client)
    service = mock_bleak_client.services[0]
    if malformation == "service":
        service.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    else:
        service.characteristics[0 if malformation == "write" else 1].properties = ["read"]
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    with pytest.raises(ConnectionError):
        flow._migration_endpoint_check(mock_bleak_client, {const.CONF_BED_TYPE: "kingkoil"})
    with pytest.raises(ConnectionError):
        await controller.async_discover_capabilities()
    mock_bleak_client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("selector", app.LAYOUTS)
@pytest.mark.parametrize("ending", ["stop", "expire"])
async def test_leased_hold_keeps_refreshing_then_ends_without_release(selector, ending):
    from tests.hold_lease_wire import leased_hold

    result = await leased_hold(
        "kingkoil" if selector == "KSBT03CK" else "kingkoil:KSBT03CL",
        lambda c: c.hold_control("head_up" if selector == "KSBT03CK" else "head_b_up", 100),
        end_after_s=0.95,
        end=ending,
    )
    assert [write.at_ms for write in result.held] == [0, 300, 600, 900]
    assert {write.data.hex() for write in result.held} == {
        "040200000001" if selector == "KSBT03CK" else "040200000004"
    }
    assert result.after == ()


async def test_shared_advertisement_offers_app_without_choosing_layout():
    from custom_components.adjustable_bed.detection import detect_new_bed
    from tests.test_detection import _make_service_info

    for name in ("KSBT03CK00000001", "prefixKSBT03CLsuffix"):
        result = detect_new_bed(_make_service_info(name=name))
        assert "kingkoil" in (result.ambiguous_types or []) or result.bed_type == "kingkoil"


@pytest.mark.parametrize("valid", [True, False])
async def test_new_setup_probe_uses_same_role_gate(hass, monkeypatch, mock_bleak_client, valid):
    from custom_components.adjustable_bed import config_flow
    from tests.test_config_flow import _fresh_gate

    client = mock_bleak_client
    client.services = gatt("b")
    if not valid:
        client.services[0].characteristics[1].properties = ["read"]
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    freshness, device = _fresh_gate("hci0", -55)
    monkeypatch.setattr(config_flow, "async_gate_connection", lambda *a, **kw: (freshness, device))
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    info = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", info)
    report = await flow._probe_capabilities(ADDRESS, "auto", "kingkoil", "KSBT03CL")
    assert report.connected is valid
    assert bool(report.error) is not valid
    info.assert_not_awaited()
    client.write_gatt_char.assert_not_called()
    client.disconnect.assert_awaited_once()


async def test_failed_role_gate_cannot_be_finished_as_success(hass):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        CapabilityReport,
    )
    from custom_components.adjustable_bed.setup_operation import OperationOutcome, OperationResult

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._pending_entry = {
        "address": ADDRESS,
        "bed_type": "kingkoil",
        "protocol_variant": "KSBT03CK",
    }
    flow._pending_title = "King Koil"
    flow.operation.result = OperationResult(
        outcome=OperationOutcome.CONNECTION_FAILED,
        payload=CapabilityReport(connected=False, kingkoil_transport_valid=False),
    )
    create = flow._async_create_selected_app_entry = AsyncMock()
    form = await flow.async_step_verify_connection()
    assert form["step_id"] == "verify_connection"
    forged = await flow.async_step_verify_connection({"action": "finish"})
    assert forged["step_id"] == "verify_connection"
    create.assert_not_awaited()


async def test_expired_scheduler_deadline_blocks_first_submit_even_before_timer_callback(
    hass, mock_bleak_client
):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    coordinator, controller = await connected(hass, mock_bleak_client)
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=coordinator.cancel_command,
        admitted_stop_epoch=0,
        intent_id="expired-before-submit",
        kind=CommandKind.HOLD,
        group_id=None,
        resources=frozenset({"motor:*"}),
        hold_deadline=asyncio.get_running_loop().time() - 1,
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        with pytest.raises(asyncio.CancelledError):
            await controller.hold_control("head_up", 300)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    mock_bleak_client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("selector", app.LAYOUTS)
async def test_real_ha_lease_renewal_and_stop(
    hass, mock_coordinator_connected, mock_bleak_client, selector
):
    client = mock_bleak_client
    client.services = gatt("b")
    e = entry(hass, selector)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    target._motor_pulse_count = 1
    registry = er.async_get(hass)
    device = next(
        item.device_id for item in registry.entities.values() if item.config_entry_id == e.entry_id
    )

    async def renew():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": device,
                "control": "head_up" if selector == "KSBT03CK" else "head_b_up",
                "duration": 0.2,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    client.write_gatt_char.reset_mock()
    with virtual_clock():
        active = asyncio.create_task(renew())
        for _ in range(6):
            await asyncio.sleep(0.1)
            await renew()
            assert not active.done()
        await target.async_stop_command()
        await active
        count = len(written(client))
        await asyncio.sleep(0.7)
        assert len(written(client)) == count
    assert count >= 2
    assert set(written(client)) == {"040200000001" if selector == "KSBT03CK" else "040200000004"}
    assert await hass.config_entries.async_unload(e.entry_id)


async def _public_stop(coordinator, controller, motor):
    if motor:
        await coordinator.async_stop_motor(
            controller.motor_control_specs[0].stop_fn, "motor:*", stream_member=False
        )
    else:
        await coordinator.async_stop_command()


@pytest.mark.parametrize("motor", [False, True], ids=["bed", "motor"])
@pytest.mark.parametrize("state", ["disconnected", "no_controller", "replacement"])
async def test_public_stop_never_prepares_a_connection(
    hass, mock_bleak_client, monkeypatch, motor, state
):
    coordinator, controller = await connected(hass, mock_bleak_client)
    coordinator._client = None
    controller.on_disconnect()
    if state == "no_controller":
        coordinator._controller = None
    elif state == "replacement":
        coordinator._client = AsyncMock(is_connected=True)
    ensure = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure)
    await _public_stop(coordinator, controller, motor)
    ensure.assert_not_awaited()
    mock_bleak_client.write_gatt_char.assert_not_called()
    if state == "replacement":
        coordinator._client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("motor", [False, True], ids=["bed", "motor"])
@pytest.mark.parametrize("lost_link", [False, True], ids=["original", "lost_link"])
async def test_public_stop_settles_original_submitted_write(
    hass, mock_bleak_client, monkeypatch, motor, lost_link
):
    coordinator, controller = await connected(hass, mock_bleak_client)
    started, finish = asyncio.Event(), asyncio.Event()

    async def slow_write(*args, **kwargs):
        started.set()
        await finish.wait()

    mock_bleak_client.write_gatt_char.side_effect = slow_write
    ensure = AsyncMock(return_value=True)
    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure)
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda c: c.hold_control("head_up", 900),
            resource="motor:*",
        )
    )
    await started.wait()
    ensure.reset_mock()
    replacement = AsyncMock(is_connected=True)
    if lost_link:
        coordinator._client = replacement
        coordinator._controller = None
    stopping = asyncio.create_task(_public_stop(coordinator, controller, motor))
    for _ in range(8):
        await asyncio.sleep(0)
    assert not stopping.done()
    finish.set()
    await stopping
    await asyncio.gather(movement, return_exceptions=True)
    ensure.assert_not_awaited()
    assert written(mock_bleak_client) == ["040200000001"]
    replacement.write_gatt_char.assert_not_called()


async def test_native_cover_and_bed_stop_service_stay_offline(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch
):
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    mock_bleak_client.services = gatt("b")
    e = entry(hass, "KSBT03CL")
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = loaded_runtime(hass, e.entry_id)
    assert coordinator is not None
    registry = er.async_get(hass)
    cover = next(
        item
        for item in registry.entities.values()
        if item.config_entry_id == e.entry_id and item.domain == "cover"
    )
    stop_button = next(
        item
        for item in registry.entities.values()
        if item.config_entry_id == e.entry_id and item.unique_id.endswith("_stop")
    )
    coordinator._client = None
    coordinator._controller = None
    mock_bleak_client.write_gatt_char.reset_mock()
    ensure = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": cover.entity_id}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": stop_button.entity_id}, blocking=True
    )
    await hass.services.async_call(
        const.DOMAIN, "stop_all", {"device_id": cover.device_id}, blocking=True
    )
    ensure.assert_not_awaited()
    mock_bleak_client.write_gatt_char.assert_not_called()
    assert await hass.config_entries.async_unload(e.entry_id)
