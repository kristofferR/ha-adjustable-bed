"""Public-path regression coverage for RÖWA Sol round-one findings."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.roewa.controller import RoewaController
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.hold_lease_wire import virtual_clock
from tests.test_roewa import client


async def runtime(hass, suffix, *, name_control=True):
    address = f"AA:BB:CC:DD:49:{suffix:02X}"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=f"RÖWA {suffix}",
        version=5,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: f"RÖWA {suffix}",
            "bed_type": "roewa",
            "protocol_variant": "remote2Drive",
            "motor_pulse_count": 1,
            "connection_mode": "always",
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    ble = client()

    async def disconnect():
        ble.is_connected = False

    ble.disconnect = AsyncMock(side_effect=disconnect)
    if not name_control:
        from custom_components.adjustable_bed.profiles.roewa import NAME_UUID

        ble.services[0].characteristics[:] = [
            c for c in ble.services[0].characteristics if c.uuid != NAME_UUID
        ]
    coordinator._client = ble
    ctrl = RoewaController(coordinator)
    coordinator._controller = ctrl
    await ctrl.async_discover_capabilities()
    from types import SimpleNamespace

    await ctrl.async_on_connect(
        SimpleNamespace(is_current=lambda: True, store_device_info=lambda *_: None)
    )
    coordinator._offline_controller = ctrl
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id,
        device_info=coordinator.device_info,
    )
    ble.write_gatt_char.reset_mock()
    return coordinator, ctrl, ble, device.id


async def test_two_target_rename_preflights_optional_endpoint_before_any_write(hass):
    await services.async_register_services(hass)
    first = await runtime(hass, 1)
    second = await runtime(hass, 2, name_control=False)
    try:
        with pytest.raises(HomeAssistantError), virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "rename",
                {
                    "device_id": [first[3], second[3]],
                    "name": "AB",
                },
                blocking=True,
            )
        first[2].write_gatt_char.assert_not_awaited()
        second[2].write_gatt_char.assert_not_awaited()
    finally:
        await first[0].async_shutdown()
        await second[0].async_shutdown()


async def test_stop_during_second_rename_preflight_prevents_every_target_write(hass):
    await services.async_register_services(hass)
    first = await runtime(hass, 51)
    second = await runtime(hass, 52, name_control=False)
    bed = second[0]
    try:
        async with bed._command_lock:
            rename = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN, "rename",
                    {"device_id": [first[3], second[3]], "name": "AB"}, blocking=True,
                )
            )
            async with asyncio.timeout(2):
                while bed.command_scheduler.active is None:
                    await asyncio.sleep(0)
            stopped = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN, "stop_all", {"device_id": [second[3]]}, blocking=True,
                )
            )
            async with asyncio.timeout(2):
                while bed.stop_epoch == 0:
                    await asyncio.sleep(0)
        await stopped
        result = await asyncio.gather(rename, return_exceptions=True)
        assert isinstance(result[0], (HomeAssistantError, asyncio.CancelledError))
        first[2].write_gatt_char.assert_not_awaited()
        second[2].write_gatt_char.assert_not_awaited()
    finally:
        await first[0].async_shutdown()
        await second[0].async_shutdown()


def setup_probe(ble):
    from tests.test_config_flow import _patch_gate

    stack = ExitStack()
    stack.enter_context(_patch_gate("hci0", -55))
    stack.enter_context(
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=ble))
    )
    stack.enter_context(
        patch("custom_components.adjustable_bed.config_flow.discover_services", AsyncMock())
    )
    stack.enter_context(
        patch("homeassistant.components.bluetooth.async_scanner_count", return_value=1)
    )
    return stack


def probe_client(problem):
    from custom_components.adjustable_bed.profiles import roewa as app

    ble = client()

    async def disconnect():
        ble.is_connected = False

    ble.disconnect = AsyncMock(side_effect=disconnect)
    if problem == "missing_feedback":
        ble.services[0].characteristics[:] = [
            c for c in ble.services[0].characteristics if c.uuid != app.FEEDBACK_UUID
        ]
    elif problem == "generic":
        ble.services[0].characteristics[:] = []
    elif problem in ("empty_firmware", "empty_model", "invalid_utf8"):

        async def read(char):
            bad = app.MODEL_UUID if problem == "empty_model" else app.FIRMWARE_UUID
            return (b"\xff" if problem == "invalid_utf8" else b"") if char.uuid == bad else b"1.0"

        ble.read_gatt_char.side_effect = read
    return ble


async def finish_probe(flow, progress):
    assert progress["type"] == "progress"
    await progress["progress_task"]
    transition = await flow.async_step_setup_progress()
    assert transition["step_id"] == "verify_connection"
    return await flow.async_step_verify_connection()


@pytest.mark.parametrize(
    "problem",
    ["valid", "generic", "missing_feedback", "empty_firmware", "empty_model", "invalid_utf8"],
)
async def test_real_finish_uses_read_only_profile_admission(hass, problem):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._async_transport_note = AsyncMock(return_value="")
    ble = probe_client(problem)
    with setup_probe(ble):
        form = await start_new_bed(flow, "typed", "roewa")
        assert form["step_id"] == "profile_questions"
        form = await flow.async_step_profile_questions({"protocol_variant": "remote2Drive"})
        assert form["step_id"] == "finish_settings"
        progress = await flow.async_step_finish_settings({CONF_NAME: "RÖWA"})
        form = await finish_probe(flow, progress)
        report = flow.operation.result.payload
        assert report.roewa_profile_valid is (problem == "valid")
        result = await flow.async_step_verify_connection({"action": "finish"})
    if problem == "valid":
        assert result["type"] == "create_entry"
    else:
        assert result["type"] == "form" and result["step_id"] == "verify_connection"
        options = next(v.config["options"] for v in result["data_schema"].schema.values())
        assert options == ["retry", "change_app"]
    ble.start_notify.assert_not_awaited()
    ble.write_gatt_char.assert_not_awaited()
    ble.disconnect.assert_awaited_once()


@pytest.mark.parametrize(
    "problem", ["valid", "missing_feedback", "empty_firmware", "empty_model", "invalid_utf8"]
)
async def test_real_reconfigure_cannot_apply_disproved_profile(hass, problem):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=5,
        title="RÖWA",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:49:71",
            CONF_NAME: "RÖWA",
            "bed_type": "roewa",
            "protocol_variant": "remote2Drive",
        },
    )
    entry.add_to_hass(hass)
    original = dict(entry.data)
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    flow._async_transport_note = AsyncMock(return_value="")
    ble = probe_client(problem)
    with setup_probe(ble):
        await flow.async_step_reconfigure()
        form = await flow.async_step_reconfigure_bed_type({"bed_type": "roewa"})
        assert form["step_id"] == "profile_questions"
        progress = await flow.async_step_profile_questions({"protocol_variant": "remote4Drive"})
        form = await finish_probe(flow, progress)
        assert form["step_id"] == (
            "migration_confirm" if problem == "valid" else "migration_check_failed"
        )
        if problem != "valid":
            result = await flow.async_step_migration_confirm({"action": "apply"})
            assert (
                result["type"] == "abort" and result["reason"] == "migration_verification_required"
            )
    assert dict(entry.data) == original
    ble.start_notify.assert_not_awaited()
    ble.write_gatt_char.assert_not_awaited()
    ble.disconnect.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["turn_on", "toggle"])
@pytest.mark.parametrize("feedback_before_dispatch", [False, True])
async def test_subscribed_ha_light_uses_newer_feedback_before_or_during_toggle(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    entrypoint,
    feedback_before_dispatch,
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.runtime_data import entry_runtime
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    mock_bleak_client.services = client().services
    mock_bleak_client.read_gatt_char.side_effect = None
    mock_bleak_client.read_gatt_char.return_value = b"1.0"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="RÖWA light",
        unique_id="AA:BB:CC:DD:49:72",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:49:72",
            CONF_NAME: "RÖWA light",
            "bed_type": "roewa",
            "protocol_variant": "remote2Drive",
            "motor_pulse_count": 1,
            "connection_mode": "always",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    entities = [
        e for e in er.async_get(hass).entities.values() if e.config_entry_id == entry.entry_id
    ]
    light = next(e for e in entities if e.domain == "light")
    receive = mock_bleak_client.start_notify.call_args.args[1]
    off = bytearray.fromhex("000b0000000000030000")
    receive(None, off)
    await hass.async_block_till_done()
    assert hass.states.get(light.entity_id).state == "off"
    observed_before_feedback = []

    async def write(_char, data, **_kwargs):
        assert bytes(data) == bytes.fromhex("040200020000")
        observed_before_feedback.append(coordinator.controller_state.get(UNDER_BED_LIGHTS_ON))
        # This report is newer than the pre-toggle sample, before write acknowledgement.
        receive(None, off)

    mock_bleak_client.write_gatt_char.reset_mock()
    mock_bleak_client.write_gatt_char.side_effect = write
    if feedback_before_dispatch:
        waiting = asyncio.Event()
        controller = coordinator.controller
        original_frame = controller._frame

        async def signal_frame(*args, **kwargs):
            waiting.set()
            await original_frame(*args, **kwargs)

        try:
            with patch.object(controller, "_frame", side_effect=signal_frame), virtual_clock():
                async with controller.ble_lock:
                    command = asyncio.create_task(
                        hass.services.async_call(
                            "light", entrypoint, {"entity_id": light.entity_id}, blocking=True,
                        )
                    )
                    await asyncio.wait_for(waiting.wait(), timeout=2)
                    receive(None, bytearray.fromhex("000b0002000000030000"))
                await command
            mock_bleak_client.write_gatt_char.assert_not_awaited()
            assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
            assert hass.states.get(light.entity_id).state == "on"
        finally:
            assert await hass.config_entries.async_unload(entry.entry_id)
        return
    with virtual_clock():
        await hass.services.async_call(
            "light",
            entrypoint,
            {"entity_id": light.entity_id},
            blocking=True,
        )
        assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is False
        assert hass.states.get(light.entity_id).state == "off"
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light.entity_id}, blocking=True
        )
    assert mock_bleak_client.write_gatt_char.await_count == 2
    assert observed_before_feedback == [None, None]
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is False
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_raw_capture_forwards_unknown_records_only_from_current_subscription(hass):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.profiles import roewa as app
    from tests.test_roewa import callback, connected

    c, coordinator = await connected(hass=hass)
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    old_callback = callback(coordinator)
    unknown = bytes.fromhex("aabbccdd")
    old_callback(None, bytearray(unknown))
    raw.assert_called_once_with(app.FEEDBACK_UUID, unknown)
    await c.stop_notify()
    old_callback(None, bytearray(unknown))
    assert raw.call_count == 1
    await c.start_notify()
    old_callback(None, bytearray(unknown))
    assert raw.call_count == 1
    callback(coordinator)(None, bytearray.fromhex("000b0003000000030000"))
    assert raw.call_count == 2
    c.on_disconnect()
    callback(coordinator)(None, bytearray(unknown))
    assert raw.call_count == 2


async def test_dispatched_toggle_without_report_invalidates_old_sample(hass):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.errors import invalid
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    bed, ctrl, ble, _ = await runtime(hass, 3)
    try:
        bed.handle_controller_state_update(UNDER_BED_LIGHTS_ON, False)
        with virtual_clock():
            await ctrl.lights_toggle()
        assert bed.controller_state[UNDER_BED_LIGHTS_ON] is None
        with pytest.raises(ServiceValidationError, match=str(invalid("light_state_unknown"))):
            await ctrl.lights_on()
        assert ble.write_gatt_char.await_count == 1
    finally:
        await bed.async_shutdown()


@pytest.mark.parametrize("problem", ["missing", "not_writable", "mtu"])
async def test_two_target_rename_live_endpoint_and_payload_preflight(hass, problem):
    from custom_components.adjustable_bed.profiles import roewa as app

    await services.async_register_services(hass)
    first = await runtime(hass, 4)
    second = await runtime(hass, 5)
    if problem == "missing":
        second[2].services[0].characteristics[:] = [
            c for c in second[2].services[0].characteristics if c.uuid != app.NAME_UUID
        ]
    elif problem == "not_writable":
        second[1]._link.rename.properties[:] = ["write-without-response"]
    else:
        first[2].mtu_size = 517
        second[2].mtu_size = 23
    try:
        with pytest.raises(HomeAssistantError), virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "rename",
                {
                    "device_id": [first[3], second[3]],
                    "name": "A" * 19,
                },
                blocking=True,
            )
        first[2].write_gatt_char.assert_not_awaited()
        second[2].write_gatt_char.assert_not_awaited()
    finally:
        await first[0].async_shutdown()
        await second[0].async_shutdown()


@pytest.mark.parametrize("ending", ["cancel", "release", "disconnect", "missing_endpoint", "mtu"])
async def test_queued_rename_keeps_its_session_endpoint_and_payload_bound(ending):
    import asyncio

    from custom_components.adjustable_bed.profiles import roewa as app
    from tests.test_roewa import connected, written

    ctrl, coordinator = await connected()
    coordinator.client.write_gatt_char.reset_mock()
    await ctrl.ble_lock.acquire()
    task = asyncio.create_task(ctrl.rename_device("AB"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    if ending == "cancel":
        coordinator.cancel_command.set()
    elif ending == "release":
        await ctrl.stop_all()
    elif ending == "disconnect":
        ctrl.on_disconnect()
    elif ending == "mtu":
        coordinator.client.mtu_size = 6
    else:
        coordinator.client.services[0].characteristics[:] = [
            c for c in coordinator.client.services[0].characteristics if c.uuid != app.NAME_UUID
        ]
    ctrl.ble_lock.release()
    results = await asyncio.gather(task, return_exceptions=True)
    assert all(
        result is None or isinstance(result, (HomeAssistantError, asyncio.CancelledError))
        for result in results
    )
    assert not written(coordinator)


async def test_cancelled_queued_toggle_does_not_invalidate_a_report(hass):
    import asyncio

    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    bed, ctrl, ble, _ = await runtime(hass, 6)
    try:
        bed.handle_controller_state_update(UNDER_BED_LIGHTS_ON, False)
        await ctrl.ble_lock.acquire()
        task = asyncio.create_task(ctrl.lights_on())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        bed.cancel_command.set()
        ctrl.ble_lock.release()
        await task
        assert bed.controller_state[UNDER_BED_LIGHTS_ON] is False
        ble.write_gatt_char.assert_not_awaited()
    finally:
        await bed.async_shutdown()


async def test_identity_read_cannot_activate_a_replaced_session():
    import asyncio
    from types import SimpleNamespace

    from custom_components.adjustable_bed.errors import BedNotConnectedError
    from tests.test_roewa import connected

    ctrl, coordinator = await connected()
    ctrl.on_disconnect()
    await ctrl.async_discover_capabilities()
    old = coordinator.client
    entered, release = asyncio.Event(), asyncio.Event()

    async def read(_char):
        entered.set()
        await release.wait()
        return b"1.0"

    old.read_gatt_char.reset_mock()
    old.start_notify.reset_mock()
    old.write_gatt_char.reset_mock()
    old.read_gatt_char.side_effect = read
    task = asyncio.create_task(ctrl.async_on_connect(SimpleNamespace(is_current=lambda: True)))
    await entered.wait()
    ctrl.on_disconnect()
    coordinator.client = client()
    release.set()
    with pytest.raises(BedNotConnectedError):
        await task
    assert old.read_gatt_char.await_count == 1
    old.start_notify.assert_not_awaited()
    old.write_gatt_char.assert_not_awaited()
    coordinator.client.read_gatt_char.assert_not_awaited()


async def test_offline_reconfigure_is_not_mistaken_for_live_disproof(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=5,
        title="RÖWA",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:49:73",
            CONF_NAME: "RÖWA",
            "bed_type": "roewa",
            "protocol_variant": "remote2Drive",
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    flow._async_transport_note = AsyncMock(return_value="")
    with patch("homeassistant.components.bluetooth.async_scanner_count", return_value=0):
        await flow.async_step_reconfigure()
        await flow.async_step_reconfigure_bed_type({"bed_type": "roewa"})
        form = await flow.async_step_profile_questions({"protocol_variant": "remote4Drive"})
    assert form["step_id"] == "migration_confirm"
    assert entry.data["protocol_variant"] == "remote2Drive"
