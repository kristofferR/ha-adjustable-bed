"""Native HA commands settle state from their own delivered frames and session."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.hestia import controller as module
from custom_components.adjustable_bed.beds.hestia.state import ALARM, MASSAGE
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import virtual_clock
from tests.test_somos import gatt

ADDRESS = "AA:BB:CC:DD:16:44"
CONTROLS = {
    "light": ("light", "under_bed_lights", UNDER_BED_LIGHTS_ON),
    "massage": ("switch", "controller_switch_hestia_massage", MASSAGE),
    "timer": ("select", "massage_timer", MASSAGE_TIMER_MINUTES),
    "alarm": ("switch", "controller_switch_hestia_alarm", ALARM),
}


@pytest.fixture
async def native(hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations):
    mock_bleak_client.services = gatt("a")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Hestia delivery",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Hestia delivery",
            const.CONF_BED_TYPE: "hestia_motion",
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime, AdjustableBedCoordinator)
    bed = runtime.controller
    assert isinstance(bed, module.HestiaController)
    bed.choose("intensity", "3")
    bed.choose("wave", "2")
    registry = er.async_get(hass)
    entities = {}
    for key, (domain, suffix, _) in CONTROLS.items():
        eid = registry.async_get_entity_id(domain, const.DOMAIN, f"{ADDRESS}_{suffix}")
        assert eid is not None
        entities[key] = eid
    try:
        yield SimpleNamespace(
            hass=hass, runtime=runtime, bed=bed, client=mock_bleak_client, entities=entities
        )
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def invoke(native, control, *, initial=False):
    domain = CONTROLS[control][0]
    service = "select_option" if control == "timer" else "turn_off" if initial else "turn_on"
    data = {"entity_id": native.entities[control]}
    if control == "timer":
        data["option"] = "10 min" if initial else "20 min"
    await native.hass.services.async_call(domain, service, data, blocking=True)


def shown(native, control):
    state = native.hass.states.get(native.entities[control])
    assert state is not None
    return state.state


async def establish(native, control):
    with virtual_clock():
        await invoke(native, control, initial=True)
    assert shown(native, control) == ("10 min" if control == "timer" else "off")
    native.client.write_gatt_char.reset_mock()
    return dict(native.bed.persisted_app_state)


@pytest.mark.parametrize("control", CONTROLS)
async def test_native_prewrite_cancel_preserves_state_cache_and_preferences(native, control):
    prior = await establish(native, control)
    entered, finish = asyncio.Event(), asyncio.Event()
    events: list[asyncio.Event] = []

    async def pause(operation, event):
        operation.close()
        events.append(event)
        entered.set()
        await finish.wait()
        if event.is_set():
            raise asyncio.CancelledError

    send = native.bed._send

    async def alarm_pending(link, frame, cancel):
        events.append(cancel)
        entered.set()
        await finish.wait()
        await send(link, frame, cancel)

    # Key controls pause inside the real prewrite100ms wait. RTC has no wait,
    # so hold it at the writer's admission boundary instead.
    with (
        patch.object(native.bed, "_send", new=alarm_pending)
        if control == "alarm"
        else patch.object(module, "cancellable", new=pause)
    ):
        task = asyncio.create_task(invoke(native, control))
        await asyncio.wait_for(entered.wait(), 1)
        try:
            assert shown(native, control) == ("10 min" if control == "timer" else "off")
        finally:
            events[0].set()
            finish.set()
            await task
    native.client.write_gatt_char.assert_not_called()
    assert shown(native, control) == ("10 min" if control == "timer" else "off")
    assert native.bed.persisted_app_state == prior
    if control == "light":
        assert native.bed._lamp is False


@pytest.mark.parametrize("control", CONTROLS)
async def test_native_backend_failure_with_no_completed_frame_preserves_known_state(
    native, control
):
    prior = await establish(native, control)
    native.client.write_gatt_char.side_effect = BleakError("no completed frame")
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await invoke(native, control)
    assert native.client.write_gatt_char.await_count == 1
    assert shown(native, control) == ("10 min" if control == "timer" else "off")
    assert native.bed.persisted_app_state == prior
    if control == "light":
        assert native.bed._lamp is False


@pytest.mark.parametrize("control", CONTROLS)
async def test_native_final_completed_frame_wins_over_late_cancel(native, control):
    prior = await establish(native, control)
    count = 2 if control == "massage" else 1

    async def cancel_after_last(*args, **kwargs):
        if native.client.write_gatt_char.await_count == count:
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()

    native.client.write_gatt_char.side_effect = cancel_after_last
    with virtual_clock():
        await invoke(native, control)
    assert native.client.write_gatt_char.await_count == count
    assert shown(native, control) == ("20 min" if control == "timer" else "on")
    assert native.runtime.controller_state[CONTROLS[control][2]] == (
        20 if control == "timer" else True
    )
    assert native.bed.persisted_app_state == (
        {**prior, "timer": "20"} if control == "timer" else prior
    )
    if control == "light":
        assert native.bed._lamp is True


@pytest.mark.parametrize("interruption", ("cancel", "second_write_failure"))
async def test_native_partial_massage_becomes_unknown_without_changing_local_choices(
    native, interruption
):
    prior = await establish(native, "massage")

    async def interrupt(*args, **kwargs):
        if interruption == "cancel":
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()
        elif native.client.write_gatt_char.await_count == 2:
            raise BleakError("intensity write failed after wave")

    native.client.write_gatt_char.side_effect = interrupt
    with virtual_clock():
        if interruption == "second_write_failure":
            with pytest.raises(HomeAssistantError):
                await invoke(native, "massage")
        else:
            await invoke(native, "massage")
    assert native.client.write_gatt_char.await_count == (1 if interruption == "cancel" else 2)
    assert shown(native, "massage") == "unknown"
    assert native.runtime.controller_state[MASSAGE] is None
    assert native.bed.persisted_app_state == prior


@pytest.mark.parametrize("control", CONTROLS)
async def test_native_old_session_completion_cannot_publish_or_remember_intent(native, control):
    prior = await establish(native, control)
    old_link = native.bed._link
    count = 2 if control == "massage" else 1

    async def replace_session(*args, **kwargs):
        if native.client.write_gatt_char.await_count == count:
            await native.bed.async_discover_capabilities()

    native.client.write_gatt_char.side_effect = replace_session
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await invoke(native, control)
    assert native.client.write_gatt_char.await_count == count
    assert native.bed._link is not old_link
    assert shown(native, control) == "unknown"
    assert native.runtime.controller_state[CONTROLS[control][2]] is None
    assert native.bed.persisted_app_state == prior
    assert native.bed._lamp is None


@pytest.mark.parametrize("control", CONTROLS)
async def test_native_failure_after_a_tracked_write_makes_intent_unknown(native, control):
    prior = await establish(native, control)
    write = native.bed._write_gatt_with_retry

    async def fail_after_write(*args, **kwargs):
        # The real writer completes and marks its own frame before the error.
        # Unlike a failed submission, this cannot keep the earlier known value.
        await write(*args, **kwargs)
        raise BleakError("operation failed after its completed frame")

    with (
        patch.object(native.bed, "_write_gatt_with_retry", new=fail_after_write),
        virtual_clock(),
        pytest.raises(HomeAssistantError),
    ):
        await invoke(native, control)
    assert native.client.write_gatt_char.await_count == 1
    assert shown(native, control) == "unknown"
    assert native.runtime.controller_state[CONTROLS[control][2]] is None
    assert native.bed.persisted_app_state == prior
    assert native.bed._lamp is None
