"""Feature state stays on the admitted lane while the local selector changes."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.kaidi.comfy import TIMER_REMAINING, TIMER_SELECTION
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.controller_state import sided
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.test_comfy import no_real_timers  # noqa: F401
from tests.test_coordinator_sleepys_elite import _FakeGattClient, _ready_command_lane


@pytest.fixture
async def feature_bed(hass, request):
    app = request.param
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=app,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            const.CONF_BED_TYPE: app,
            const.CONF_PRODUCT_TYPE: 130,
            const.CONF_KAIDI_ROOM_ID: 10001,
            const.CONF_KAIDI_SOFA_ACU_NO: 0xF322,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    client = _FakeGattClient()
    co._client = client
    c = await create_controller(co, app, None, client)
    c._ready, c._own, c._target = True, 0x11223344, 0x12345678
    co._controller = c
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = co
    await co._async_restore_app_state(c)
    await async_register_services(hass)
    selects = {e.translation_key: e for e in _select_entities_for(hass, co)}
    light = next(
        e for e in _switch_entities_for(hass, co) if e.entity_description.key == "under_bed_lights"
    )
    with (
        _ready_command_lane(co),
        patch.object(light, "async_write_ha_state"),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(co, const.SIDE_BOTH)], []),
        ),
    ):
        unregister = co.register_controller_state_callback(light._handle_controller_state_update)
        try:
            yield co, c, client, selects, light
        finally:
            unregister()
            c._stop_countdown()
            await co.async_shutdown()


@pytest.mark.parametrize("feature_bed", ("komfyd", "comfyds"), indirect=True)
async def test_reconnect_hands_off_offline_countdown(feature_bed):
    co, controller, client, _, light = feature_bed
    retired = []
    try:
        await controller.control("timer_start")
        for _ in range(2):
            countdown = controller._countdown
            assert countdown is not None
            controller.on_disconnect()
            co._controller = None
            controller._tick()
            assert countdown.cancelled()
            offline_countdown = controller._countdown
            assert offline_countdown is not None and not offline_countdown.cancelled()
            assert co.controller_state[TIMER_REMAINING] > 0

            retired.append(controller)
            controller = await create_controller(co, co.bed_type, None, client)
            co._controller = controller
            await co._async_restore_app_state(controller)
            controller._ready, controller._own, controller._target = True, 0x11223344, 0x12345678
            assert offline_countdown.cancelled()
            assert all(old._countdown is None for old in retired)
            assert controller._countdown is not None
            assert co.controller_state[TIMER_REMAINING] > 0

        await controller.control("timer_stop")
        await controller.select_side("right")
        await light.async_turn_on()
        assert controller._countdown is None
        assert co.controller_state[TIMER_REMAINING] == 0
        assert co.controller_state[UNDER_BED_LIGHTS_ON] is True
        assert all(old._countdown is None for old in retired)
    finally:
        controller._stop_countdown()


@pytest.mark.parametrize("feature_bed", ("komfyd", "comfyds"), indirect=True)
@pytest.mark.parametrize(
    "action", ("light_on", "light_off", "timer_30", "timer_start", "timer_stop")
)
@pytest.mark.parametrize("blocked_at", ("session", "gatt", "pacing"))
@pytest.mark.parametrize("outcome", ("success", "failed", "cancelled"))
async def test_pending_feature_keeps_admitted_lane(hass, feature_bed, action, blocked_at, outcome):
    co, c, client, selects, light = feature_bed
    side = selects["comfy_selected_side"]
    await side.async_select_option("left")
    c._led = [action == "light_off", action == "light_off", False]
    c._timer_minutes = [20, 40, 50]
    c._timer_started = [
        time.time() - 60 if action == "timer_stop" else 0,
        time.time() - 120 if action in ("timer_start", "timer_stop") else 0,
        0,
    ]
    c._save_local()
    initial = dict(c.persisted_app_state)
    entered, release = asyncio.Event(), asyncio.Event()
    command_cancel: asyncio.Event | None = None
    frames = []

    async def write(_uuid, frame, **_kwargs):
        frames.append(bytes(frame))
        if blocked_at == "gatt":
            entered.set()
            await release.wait()
        if outcome == "failed":
            raise ConnectionError("injected write failure")
        if outcome == "cancelled":
            raise asyncio.CancelledError

    client.write_gatt_char.side_effect = write

    async def invoke():
        if action.startswith("light_"):
            await (light.async_turn_on() if action == "light_on" else light.async_turn_off())
        elif action == "timer_30":
            await selects["comfy_timer_selection"].async_select_option("30")
        else:
            await hass.services.async_call(
                const.DOMAIN,
                "comfy_control",
                {"device_id": ["bed"], "action": action},
                blocking=True,
            )

    # Block real controller awaits without waiting on protocol timers.
    if blocked_at == "session":
        await c._session_lock.acquire()
        original_session = c._ensure_session

        async def session():
            entered.set()
            await original_session()

        send_patch = patch.object(c, "_ensure_session", side_effect=session)
    elif blocked_at == "pacing":
        await c._write_lane.acquire()
        original_send = c._send_opcode

        async def send(opcode, **kwargs):
            nonlocal command_cancel
            command_cancel = co.cancel_command
            entered.set()
            await original_send(opcode, **kwargs)

        send_patch = patch.object(c, "_send_opcode", side_effect=send)
    else:
        send_patch = patch.object(c, "_send_opcode", wraps=c._send_opcode)
    started_at = time.time()
    with send_patch:
        operation = asyncio.create_task(invoke())
        try:
            await entered.wait()
            await side.async_select_option("right")
            assert not operation.done()  # The actual local entity bypasses BLE serialization.
            selected_view = dict(co.controller_state)
            if blocked_at == "session":
                c._session_lock.release()
            if blocked_at == "pacing":
                if outcome == "cancelled":
                    assert command_cancel is not None
                    command_cancel.set()
                c._write_lane.release()
            release.set()
            if outcome == "success":
                await operation
            else:
                await asyncio.gather(operation, return_exceptions=True)
        finally:
            release.set()
            if c._write_lane.locked() and blocked_at == "pacing":
                c._write_lane.release()
            if c._session_lock.locked() and blocked_at == "session":
                c._session_lock.release()
            await asyncio.gather(operation, return_exceptions=True)

    expected = {**initial, "side": 2}
    if outcome == "success":
        if action.startswith("light_"):
            expected["led"] = [action == "light_on", initial["led"][1], False]
        elif action == "timer_30":
            expected["timer_minutes"] = [30, 40, 50]
        elif action == "timer_start":
            assert started_at <= c._timer_started[0] <= time.time()
            expected["timer_started"] = [c._timer_started[0], initial["timer_started"][1], 0]
        else:
            expected["timer_started"] = [0, initial["timer_started"][1], 0]
    else:
        assert dict(co.controller_state) == selected_view
    assert dict(c.persisted_app_state) == expected
    assert await co._app_state_store.async_slot(co._app_state_slots[c]) == expected
    assert [frame[11] for frame in frames] == (
        [] if outcome == "cancelled" and blocked_at == "pacing" else [c.profile.commands[action][0]]
    )
    state = co.controller_state
    assert state[UNDER_BED_LIGHTS_ON] == initial["led"][1]
    assert light.is_on == initial["led"][1]
    assert state[sided(UNDER_BED_LIGHTS_ON, "left")] == expected["led"][0]
    assert state[TIMER_SELECTION] == "40"
    assert state[sided(TIMER_SELECTION, "left")] == str(expected["timer_minutes"][0])
    for lane, key in ((0, sided(TIMER_REMAINING, "left")), (1, TIMER_REMAINING)):
        remaining = (
            max(
                0,
                int(
                    expected["timer_minutes"][lane] * 60
                    - (time.time() - expected["timer_started"][lane])
                ),
            )
            if expected["timer_started"][lane]
            else 0
        )
        assert abs(state[key] - remaining) <= 1
