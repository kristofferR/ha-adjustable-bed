"""Quick-mode polling, side-specific onboarding and shared status receivers."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_IDLE_DISCONNECT_SECONDS,
    DOMAIN,
)
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.motion_bed_state import (
    MotionBedContext,
    MotionBedRoute,
    MotionBedState,
    parse_motion_bed_notification,
)
from tests.test_motion_bed_lifecycle import real_coordinator
from tests.test_paired_setup import _paired_entry_data


@pytest.mark.parametrize("ending", ["cancel", "drop", "module"])
async def test_thermal_poll_owns_quick_handoff_and_queued_idle_cleanup(hass, monkeypatch, ending):
    coord = await real_coordinator(hass, "TL-Q" if ending == "module" else "TL-W")
    controller, client = coord.controller, coord.client
    assert isinstance(controller, MotionBedController)
    coord._disconnect_after_command = True
    real_sleep = asyncio.sleep
    entered, first_query, polling = asyncio.Event(), asyncio.Event(), asyncio.Event()
    delays = []

    async def sleep(delay):
        delays.append(delay)
        if delay == 2:
            entered.set()
            await first_query.wait()
        elif delay == 5:
            polling.set()
            await asyncio.Event().wait()
        else:
            await real_sleep(0)

    async def disconnect():
        client.is_connected = False
        coord._on_disconnect(client)

    client.disconnect = AsyncMock(side_effect=disconnect)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr(controller, "_startup", lambda: MotionBedController._startup(controller))
    coord._reset_disconnect_timer()
    prearmed = coord._disconnect_timer
    assert prearmed is not None
    await coord.async_execute_controller_command(lambda c: c.start_notify())
    receive = client.start_notify.call_args.args[1]
    if ending == "module":
        receive(client.start_notify.call_args.args[0], bytearray.fromhex("FFFFFFFF01002714000000000000000C"))
    try:
        for _ in range(30):
            if entered.is_set():
                break
            await real_sleep(0)
        assert entered.is_set()
        assert prearmed.cancelled()
        assert coord._command_connection_holds == 1
        assert coord._disconnect_timer is None
        # A previously queued idle callback must recheck the live hold under lock.
        await coord._command_lock.acquire()
        idle = asyncio.create_task(coord._async_idle_disconnect())
        await real_sleep(0)
        coord._command_lock.release()
        await idle
        client.disconnect.assert_not_awaited()
        first_query.set()
        for _ in range(30):
            if polling.is_set():
                break
            await real_sleep(0)
        assert polling.is_set()
        assert [d for d in delays if d in (2, 5)] == [2, 5]
        assert client.write_gatt_char.await_args.args[1] == SOURCE_COMMANDS["LengnuanFragment:58"]
        task = controller._thermal_task
        assert task is not None
        if ending == "drop":
            client.is_connected = False
            coord._on_disconnect(client)
        elif ending == "module":
            frame = bytearray.fromhex("FFFFFFFF01002714000000000000000C")
            frame[12] = 11
            receive(client.start_notify.call_args.args[0], frame)
            await coord.async_execute_controller_command(lambda c: c.set_motion_bed_surface("air"))
        else:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(10):
            await real_sleep(0)
        assert coord._command_connection_holds == 0
        assert task.done()
        thermal_queries = [c for c in client.write_gatt_char.await_args_list if c.args[1] == SOURCE_COMMANDS["LengnuanFragment:58"]]
        assert len(thermal_queries) == 1
        if ending == "drop":
            assert coord.controller is None and coord.client is None
            assert coord._disconnect_timer is None
        else:
            assert coord._disconnect_timer is not None
    finally:
        tasks = tuple(controller._tasks)
        await controller.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)
        coord._cancel_disconnect_timer()


async def test_other_two_address_pair_cannot_enter_motion_before_rerender(hass):
    data = _paired_entry_data()
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    original = entry.data
    result = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_MOTION_BED}, step_id="settings")
    assert result["errors"] == {CONF_BED_TYPE: "app_profile_unpair_first"}
    assert not flow._pending_changed_data
    assert entry.data == original


async def test_valid_motion_pair_common_options_preserve_independent_names(hass):
    data = _paired_entry_data()
    data[CONF_BED_TYPE] = BED_TYPE_MOTION_BED
    for child, name in zip(data["pair_children"], ("QMS-IQ", "TL-B"), strict=True):
        child[CONF_BED_TYPE] = BED_TYPE_MOTION_BED
        child[CONF_BLE_DEVICE_NAME] = name
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form({CONF_IDLE_DISCONNECT_SECONDS: 60}, step_id="settings")
    assert result["type"] == "create_entry", result
    assert [c[CONF_BLE_DEVICE_NAME] for c in entry.data["pair_children"]] == ["QMS-IQ", "TL-B"]
    assert all(c[CONF_BED_TYPE] == BED_TYPE_MOTION_BED for c in entry.data["pair_children"])


@pytest.mark.parametrize("contexts", [
    frozenset({"smart_sleep", "calibration"}),
])
@pytest.mark.parametrize("raw,field,value", [
    ("FFFFFFFF02000A1400000A46", "calibration_side", 140),
])
def test_each_complete_shared_status_receiver_survives_shorter_reply(contexts, raw, field, value):
    result = parse_motion_bed_notification(bytes.fromhex(raw), MotionBedRoute(contexts=contexts), MotionBedState())
    assert result.rejection is None
    assert getattr(result.state, field) == value
    assert result.state.sleep_enabled is None
    assert result.state.night_light_enabled is None


@pytest.mark.parametrize("context,raw", [
    ("smart_sleep", "FFFFFFFF02000A140000000000000F00010100"),
    ("calibration", "FFFFFFFF02000A1400000A46"),
])
def test_single_status_receiver_preserves_its_underlength_rejection(context: MotionBedContext, raw):
    state = MotionBedState(calibration_side=12, sleep_enabled=True)
    result = parse_motion_bed_notification(bytes.fromhex(raw)[:-1], MotionBedRoute(contexts=frozenset({context})), state)
    assert result.rejection == "underlength" and result.state == state


@pytest.mark.parametrize("context,raw,field,value", [
    ("calibration", "FFFFFFFF02000A1400000A46", "calibration_side", 140),
])
async def test_real_home_notify_keeps_complete_extra_status_context(hass, context: MotionBedContext, raw, field, value):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller, client = coord.controller, coord.client
    await controller.start_notify()
    controller._activate(context)
    receive = client.start_notify.call_args.args[1]
    receive(client.start_notify.call_args.args[0], bytearray.fromhex(raw))
    assert controller.protocol_diagnostics["last_notification_rejection"] is None
    assert controller.protocol_diagnostics[field] == value
    await controller.stop_notify()
    coord._cancel_disconnect_timer()
