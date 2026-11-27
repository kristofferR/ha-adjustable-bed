"""Actual setup, entity surfaces and coordinator delivery/session boundaries."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.flexispot import controller as ctrl
from custom_components.adjustable_bed.codec import flexispot as codec
from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PRODUCT_TYPE, DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import flexispot as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.form_helpers import complete, form_fields
from tests.test_linx import _Characteristic, _Services
from tests.test_setup_routes import _typed


class _Service:
    uuid = codec.SERVICE

    def __init__(self):
        self.characteristics = [
            _Characteristic(codec.WRITE, ["write"], 1),
            _Characteristic(codec.NOTIFY, ["notify"], 2),
        ]

    def get_characteristic(self, uuid):
        return next((c for c in self.characteristics if c.uuid == uuid), None)


async def target(hass, model="eb632"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Flexispot",
        unique_id="AA:BB:CC:65:00:01",
        data={
            CONF_ADDRESS: "AA:BB:CC:65:00:01",
            CONF_NAME: "Bed",
            CONF_BED_TYPE: "flexispot",
            CONF_PRODUCT_TYPE: model,
            "motor_count": len(app.PROFILES[model].motors),
            "has_massage": True,
            "disable_angle_sensing": True,
            "connection_mode": "always",
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    client = SimpleNamespace(
        is_connected=True,
        services=_Services([_Service()]),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    coord._client = client
    bed = await create_controller(coord, "flexispot", "auto", client)
    coord._controller = coord._offline_controller = bed
    await bed.async_discover_capabilities()
    await bed.start_notify()
    coord._ready = True
    hass.data.setdefault("a65_targets", []).append(coord)
    return coord, bed, client


@pytest.fixture(autouse=True)
async def cleanup(hass, monkeypatch):
    monkeypatch.setattr(app, "RELEASE_MS", 0)
    monkeypatch.setattr(app, "MASSAGE_STEP_MS", 0)
    yield
    for coord in hass.data.get("a65_targets", []):
        await coord.async_shutdown()


def frames(client):
    return [bytes(c.args[1]) for c in client.write_gatt_char.call_args_list]


def notify(bed, raw=None):
    raw = raw or bytes.fromhex("9b002701651e02061eff01072d8002239500009d")
    bed._notification(bed._link, bytearray(raw))


@pytest.mark.parametrize("model", app.PROFILES)
async def test_setup_product_is_required_and_derives_capabilities(
    hass, enable_custom_integrations, model
):
    result = await _typed(hass, "flexispot")
    assert result["step_id"] == "profile_questions"
    keys = {str(marker.schema) for marker in form_fields(result["data_schema"])}
    assert CONF_PRODUCT_TYPE in keys
    with patch(
        "custom_components.adjustable_bed.config_flow.AdjustableBedConfigFlow._verification_possible",
        return_value=False,
    ):
        result = await complete(hass, result, {"profile_questions": {CONF_PRODUCT_TYPE: model}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["motor_count"] == len(app.PROFILES[model].motors)
    assert result["data"]["has_massage"] is True
    assert result["data"]["has_light"] is app.PROFILES[model].light
    assert CONF_PRODUCT_TYPE in per_side_profile("flexispot", None).keys


@pytest.mark.parametrize("model", app.PROFILES)
async def test_entity_actions_are_exact_model_commands(hass, model):
    coord, bed, client = await target(hass, model)
    profile = app.PROFILES[model]
    assert len(bed.motor_control_specs) == len(profile.motors)
    from custom_components.adjustable_bed.bed_traits import reads_positions

    assert not reads_positions(coord.entry.data)
    assert bed.supports_lights is profile.light
    assert bed.supports_single_address_pairing is False
    assert bed.execution.declared == {"hold"}
    for spec in bed.controller_button_specs:
        client.write_gatt_char.reset_mock()
        await coord.async_execute_controller_command(lambda c, spec=spec: spec.press_fn(c))
        sent = frames(client)
        assert len(sent) == 1
        assert sent[0] == codec.frame(sent[0][2], sent[0][3])
        if spec.key.startswith("save_"):
            assert sent[0][2] == 6
            assert spec.requires_confirmation and spec.hold is None
        if "right_" in spec.key:
            assert sent[0][3] & 128
    if profile.light:
        await coord.async_execute_controller_command(lambda c: c.lights_on())
        assert frames(client)[-1] == codec.frame(4, 1)
        assert coord.controller_state[UNDER_BED_LIGHTS_ON] is True
    await coord.async_execute_controller_command(lambda c: c.set_massage_timer(0))
    assert frames(client)[-1] == codec.frame(15, 0)
    assert bed.massage_timer_can_turn_off is False


async def test_right_motion_has_key_03_and_exact_cleanup(hass):
    coord, bed, client = await target(hass, "eb803")
    await coord.async_execute_controller_command(lambda c: c.hold_control("right_back_up", 1))
    assert frames(client) == [codec.frame(1, 3), codec.frame(3, 3)]


async def test_cancel_before_first_frame_and_expiry_waiting_for_ble_lane(hass):
    coord, bed, client = await target(hass)
    async with bed._ble_lock:
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda c: c.hold_control("back_up", 5))
        )
        await asyncio.sleep(0.02)
    await task
    assert frames(client) == []
    coord.cancel_command.set()
    await bed.hold_control("back_up", 1)
    assert frames(client) == []


async def test_cancel_inflight_write_settles_before_original_release(hass):
    coord, bed, client = await target(hass)
    started, finish = asyncio.Event(), asyncio.Event()
    events = []

    async def write(_char, frame, **_kwargs):
        if frame[2] == 1:
            events.append("motion started")
            started.set()
            await finish.wait()
            events.append("motion settled")
        else:
            events.append("release")

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.hold_control("back_up", 500))
    )
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert events == ["motion started"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["motion started", "motion settled", "release"]


async def test_reconnect_never_moves_cleanup_or_old_notifications_to_new_link(hass):
    coord, bed, client = await target(hass)
    original = bed._link
    replacement = SimpleNamespace(**vars(client))
    replacement.write_gatt_char = AsyncMock()

    async def write(_char, _frame, **_kwargs):
        coord._client = replacement
        await bed.async_discover_capabilities()

    client.write_gatt_char.side_effect = write
    await coord.async_execute_controller_command(lambda c: c.hold_control("back_up", 1))
    assert frames(replacement) == []
    bed._notification(original, bytearray(codec.frame(4, 1)))
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is None


async def test_failed_or_cancelled_delivery_does_not_publish_commanded_state(hass):
    coord, bed, client = await target(hass)
    client.write_gatt_char.side_effect = ConnectionError("link lost")
    with pytest.raises(ConnectionError):
        await coord.async_execute_controller_command(lambda c: c.massage_power(True))
    assert coord.controller_state.get(ctrl.POWER) is None
    client.write_gatt_char.side_effect = None
    async with bed._ble_lock:
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda c: c.massage_power(True))
        )
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert coord.controller_state.get(ctrl.POWER) is None


async def test_feedback_and_relative_levels_remain_unknown_until_report(hass):
    coord, bed, client = await target(hass, "eb803")
    with pytest.raises(ServiceValidationError, match="Wait for the bed"):
        await bed.set_level("right", 3.0)
    notify(bed)
    assert coord.controller_state[ctrl.LEVELS["right"]] == 2
    await coord.async_execute_controller_command(lambda c: c.set_level("right", 4.0))
    assert frames(client) == [codec.frame(12, 128)] * 2
    assert coord.controller_state[ctrl.LEVELS["right"]] is None
    bed.on_disconnect()
    assert coord.controller_state[ctrl.MODE] is None


async def test_snore_preserves_packed_settings_and_source_crossed_angle_rule(hass):
    coord, bed, client = await target(hass, "eb803")
    notify(bed)
    # Sensitivity pair5 -> (1,1); angle pair9 -> (2,2).
    await coord.async_execute_controller_command(lambda c: c.set_snore("right", "angle", "8"))
    assert frames(client) == [codec.snore(3, codec.pair(1, 0), 5)]
    assert coord.controller_state[ctrl.GLOBAL_SNORE] is None
    with pytest.raises(ServiceValidationError):
        await bed.set_snore("left", "enabled", False)
    notify(bed)
    await coord.async_execute_controller_command(lambda c: c.set_snore("left", "enabled", False))
    assert frames(client)[-1] == codec.snore(2, 9, 5)


async def test_alarm_preserves_other_slot_checks_weekdays_and_overlap(hass):
    coord, bed, client = await target(hass, "eb803")
    request = AlarmRequest(
        enabled=True,
        hour=9,
        minute=10,
        weekdays=(0, 6),
        slot=2,
        wake_action="wake_mode_2",
        reference_time=datetime.now(),
    )
    with pytest.raises(ServiceValidationError):
        await bed.configure_alarm(request)
    notify(bed)
    await coord.async_execute_controller_command(lambda c: c.configure_alarm(request))
    assert frames(client) == [
        codec.alarm((codec.Alarm(6, 30, 255, 1), codec.Alarm(9, 10, 193, 2)), 2, 1)
    ]
    notify(bed)
    with pytest.raises(ServiceValidationError, match="more than 20"):
        await bed.configure_alarm(
            AlarmRequest(
                enabled=True,
                hour=6,
                minute=50,
                weekdays=(0,),
                slot=2,
                reference_time=datetime.now(),
            )
        )
    with pytest.raises(ServiceValidationError):
        await bed.configure_alarm(AlarmRequest(enabled=True, reference_time=datetime.now()))


async def test_public_stop_waits_for_write_then_releases_only_started_motor(hass):
    coord, bed, client = await target(hass, "eb803")
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, frame, **_kwargs):
        if frame[2] == 1:
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.hold_control("right_back_up", 5000))
    )
    await started.wait()
    stop = asyncio.create_task(coord.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await stop
    await movement
    assert frames(client) == [
        codec.frame(1, 3),
        codec.frame(3, 3),
        *[codec.frame(3, motor) for _, motor in app.PROFILES["eb803"].motors],
    ]
    client.write_gatt_char.reset_mock()
    await coord.async_stop_command()
    assert frames(client) == [codec.frame(3, motor) for _, motor in app.PROFILES["eb803"].motors]


async def test_shared_alarm_service_routes_and_revalidates_live_snapshot(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.services import async_register_services

    coord, bed, client = await target(hass, "eb803")
    coord.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[coord.entry.entry_id] = coord
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=coord.entry.entry_id, device_info=coord.device_info
    )
    await async_register_services(hass)
    notify(bed)
    await hass.services.async_call(
        DOMAIN, "set_alarm", {"device_id": [device.id], "enabled": False, "slot": 2}, blocking=True
    )
    assert frames(client) == [
        codec.alarm((codec.Alarm(6, 30, 255, 1), codec.Alarm(7, 45, 0, 2)), 2, 1)
    ]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {"device_id": [device.id], "enabled": False, "slot": 1},
            blocking=True,
        )
    assert len(frames(client)) == 1


async def test_live_gatt_roles_validate_service_properties_and_write_mode(hass):
    coord, bed, client = await target(hass)
    original = client.services[0]
    original.uuid = "0000ffff-0000-1000-8000-00805f9b34fb"
    with pytest.raises(ConnectionError):
        await bed.async_discover_capabilities()
    original.uuid = codec.SERVICE
    original.characteristics[0].properties = ["write-without-response"]
    await bed.async_discover_capabilities()
    await coord.async_execute_controller_command(lambda c: c.massage_power(True))
    assert client.write_gatt_char.call_args.kwargs["response"] is False
    assert client.write_gatt_char.call_args.args[0] is original.characteristics[0]
    original.characteristics[1].properties = ["read"]
    with pytest.raises(ConnectionError):
        await bed.async_discover_capabilities()


def test_discovery_name_is_case_sensitive_substring_without_model_inference():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name="prefixW_LeGe123"))
    assert "flexispot" in (result.bed_type, *(result.ambiguous_types or ()))
    assert result.confidence < 0.5
    result = detect_bed_type_detailed(_make_service_info(name="w_lege123"))
    assert "flexispot" not in (result.bed_type, *(result.ambiguous_types or ()))


async def test_v0_memory_order_and_programming_are_not_numeric_key_order(hass):
    coord, bed, client = await target(hass)
    for slot, key in ((1, 1), (2, 3), (3, 2)):
        await coord.async_execute_controller_command(lambda c, slot=slot: c.preset_memory(slot))
        await coord.async_execute_controller_command(lambda c, slot=slot: c.program_memory(slot))
        assert frames(client)[-2:] == [codec.frame(7, key), codec.frame(6, key)]


async def test_renewable_hold_streams_past_finite_pulses_and_expiry_releases():
    from tests.hold_lease_wire import intervals, leased_hold

    held = codec.frame(1, 1)

    def operation(controller):
        return controller.move_back_up()

    renewable = await leased_hold("flexispot", operation, end_after_s=2, end="expire")
    finite = await leased_hold("flexispot", operation, end_after_s=2, end="expire", leased=False)
    motion = tuple(write for write in (*renewable.held, *renewable.after) if write.data == held)
    finite_motion = tuple(write for write in (*finite.held, *finite.after) if write.data == held)
    assert len(motion) > len(finite_motion)
    assert all(200 <= gap <= 210 for gap in intervals(motion))
    assert [write.data for write in renewable.after] == [codec.frame(3, 1)]


async def test_movement_and_relative_step_pacing_absorb_gatt_roundtrip(hass, monkeypatch):
    from tests.hold_lease_wire import virtual_clock

    monkeypatch.setattr(app, "MASSAGE_STEP_MS", 200)
    coord, bed, client = await target(hass, "eb803")
    with virtual_clock() as clock:
        events = []

        async def write(_char, frame, **_kwargs):
            events.append((round(clock.now * 1000), frame))
            await asyncio.sleep(0.03)

        client.write_gatt_char.side_effect = write
        await coord.async_execute_controller_command(lambda c: c.hold_control("right_back_up", 500))
        motion = [at for at, frame in events if frame[2] == 1]
        assert len(motion) == 3
        assert [b - a for a, b in zip(motion, motion[1:], strict=False)] == [200, 200]
        events.clear()
        notify(bed)
        await coord.async_execute_controller_command(lambda c: c.set_level("right", 5.0))
        steps = [at for at, frame in events]
        assert len(steps) == 3
        assert [b - a for a, b in zip(steps, steps[1:], strict=False)] == [200, 200]
