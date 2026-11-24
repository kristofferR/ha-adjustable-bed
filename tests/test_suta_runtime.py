"""Actual HA flow, factory, entities, services and scheduler callers for SUTA."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.suta import controller as bed
from custom_components.adjustable_bed.beds.suta import services as suta_services
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import suta as codec
from custom_components.adjustable_bed.command_scheduler import CommandKind
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.profiles.suta import service_for_name
from tests.error_helpers import raises_key
from tests.form_helpers import finish_new_bed
from tests.test_richmat_family_flow import setup_flow
from tests.test_suta import clock as clock


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    name = getattr(request, "param", "SUTA-B803")
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="SUTA display title",
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:28", CONF_NAME: "SUTA display title",
              const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: name,
              const.CONF_HAS_MASSAGE: False, const.CONF_DISABLE_ANGLE_SENSING: True,
              const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE},
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    tx = SimpleNamespace(uuid="suta-property-write", properties=["write"], handle=28, descriptors=[])
    rx = SimpleNamespace(uuid="suta-property-notify", properties=["notify"], handle=29, descriptors=[])
    service = SimpleNamespace(uuid=service_for_name(name), characteristics=[rx, tx])
    mock_bleak_client.services.get_service.side_effect = lambda uuid: service if uuid == service.uuid else None
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client._backend = None
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, bed.SutaController)
    await services.async_register_services(hass)
    with patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


def written(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


async def action(hass, key, **fields):
    await hass.services.async_call(const.DOMAIN, "suta", {"device_id": "bed", "action": key, **fields}, blocking=True)


async def test_actual_factory_cover_timed_hold_and_saved_entity(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.SutaController)
    assert ctrl.profile.key == "MattressControllerB803Fragment"
    save = next(entity for entity in _button_entities_for(hass, target) if entity.unique_id.endswith("program_memory_3"))
    # The card offers a memory save only in Set mode; it needs no second prompt.
    assert "requires_confirmation" not in save.extra_state_attributes
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    await cover.async_open_cover()
    assert written(client)[0] == codec.text("AT+CTRL=BOTH BACK UP")
    assert written(client)[-2:] == [codec.text("AT+CTRL=BOTH STOP")] * 2
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "bed", "motor": "back", "direction": "down", "duration_ms": 250}, blocking=True)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK DOWN")] * 2 + [codec.text("AT+CTRL=BOTH STOP")] * 2
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "hold_control", {"device_id": "bed", "control": "ctrl_back_up", "duration": 0.1}, blocking=True)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_all_targets_validate_before_any_connect_or_effect(hass, runtime):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    wrong, _ = fake_target(name="other family")
    resolve.return_value = ([(target, "both"), (wrong, "both")], [])
    with raises_key("action_for_other_beds", ServiceValidationError):
        await action(hass, "both_tv")
    assert not target.is_connected
    assert not written(client)


async def test_stop_during_lazy_import_invalidates_original_admission(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    original = suta_services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        await original(*args, **kwargs)

    with patch.object(suta_services, "async_import_modules", importing):
        await action(hass, "both_tv")
    assert written(client) == [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_actual_stop_drains_submitted_movement_and_owns_one_cleanup(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    started, finish = asyncio.Event(), asyncio.Event()

    async def block_first(_char, packet, **kwargs):
        if packet == codec.text("AT+CTRL=BOTH BACK UP"):
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = block_first
    task = asyncio.create_task(target.async_execute_controller_command(lambda c: c.hold_control("ctrl_back_up", 1000)))
    await started.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(task, stop)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


@pytest.mark.parametrize("runtime", ["SUTA-MOON", "SUTA-TEMP", "SUTA-RBHC"], indirect=True)
async def test_binary_or_feedback_routes_through_real_connect(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.SutaController)
    if ctrl.family == "MOON":
        assert len(written(client)) == 3
        client.write_gatt_char.reset_mock()
        await action(hass, "massage_timer_10", logical_side="right")
        assert written(client) == [codec.binary(0x96, 2, bytes((2, 10)))]
    elif ctrl.family == "TEMP":
        assert written(client) == [codec.binary(0xA1, 5, b"\x0f"), codec.binary(0xA0, 1, b"\x0f")]
        client.write_gatt_char.reset_mock()
        await action(hass, "temperature_setpoint", logical_side="left", value=22)
        assert written(client) == [codec.binary(0xA1, 3, bytes((1, 22)))]
    else:
        sender, callback = client.start_notify.call_args.args
        callback(sender, bytearray.fromhex("00000afffe0014ffff"))
        assert ctrl.observations == {"back": 10, "extra_1_raw": -2, "foot": 20, "extra_2_raw": -1}


async def test_text_alarm_and_active_zone_level_use_proven_schedules(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    await hass.services.async_call(const.DOMAIN, "set_alarm", {
        "device_id": "bed", "enabled": True, "time": "06:30:00", "weekdays": ["saturday", "sunday"],
    }, blocking=True)
    # Sunday is day 0 on the wire; repeating days carry the app's Loop flag.
    assert written(client) == [codec.text("AT+SA=00063001")] * 3 + [codec.text("AT+SA=06063001")] * 3 + [codec.text("AT+GA")] * 3
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "set_alarm", {
        "device_id": "bed", "enabled": False, "time": "06:30:00", "weekdays": ["sunday"],
    }, blocking=True)
    assert written(client) == [codec.text("AT+CA=00063001")] * 3 + [codec.text("AT+GA")] * 3
    # The bed finds the alarm to turn off by its time, so a time is required.
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(const.DOMAIN, "set_alarm", {
            "device_id": "bed", "enabled": False, "weekdays": ["sunday"],
        }, blocking=True)
    assert raised.value.translation_key == "alarm_time_required_to_turn_off"
    assert not written(client)
    client.write_gatt_char.reset_mock()
    await action(hass, "mass_head_dt", suffix="20")
    await action(hass, "mass_foot_dt", suffix="33")
    client.write_gatt_char.reset_mock()
    await action(hass, "mass_head_lv", suffix="10")
    assert written(client) == [codec.text("AT+MASS=BOTH HEAD LV10"), codec.text("AT+MASS=BOTH FOOT LV10")]


async def test_sequential_both_renewable_lease_rejects_before_claims(hass, runtime):
    from tests.test_paired_coordinator import _pair

    target, client, resolve = runtime
    pair, left, right = _pair([], mode=const.PAIR_CONNECTION_MODE_SEQUENTIAL)
    pair.hass = hass
    left.capability_controller = target.capability_controller
    right.capability_controller = target.capability_controller
    left.claim_hold_lease = MagicMock()
    right.claim_hold_lease = MagicMock()
    resolve.return_value = ([(pair, "both")], [])
    with pytest.raises(ServiceValidationError, match="one side"):
        await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "pair", "motor": "back", "direction": "up", "duration_ms": 1000, "hold_owner": "card", "hold_generation": 1}, blocking=True)
    left.claim_hold_lease.assert_not_called()
    right.claim_hold_lease.assert_not_called()
    assert not written(client)


async def test_new_install_and_configure_keep_raw_name_and_rebuild_factory(hass):
    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: "SUTA-TEMP"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_BLE_DEVICE_NAME: "SUTA-TEMP"})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BLE_DEVICE_NAME] == "SUTA-TEMP"
    assert data[const.CONF_HAS_MASSAGE] is False
    entry = MockConfigEntry(domain=const.DOMAIN, title="Friendly bed", data=data)
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.handler = entry.entry_id
    options.hass = hass
    # Configure uses the same persisted question and never a display-name guess.
    from custom_components.adjustable_bed.setup_questions import setup_profile
    profile = setup_profile(data[const.CONF_BED_TYPE])
    assert profile is not None
    assert any(q.key == const.CONF_BLE_DEVICE_NAME for q in profile.questions)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, "suta", "auto", None)
    assert controller.profile.key == "TempControllerFragment"

async def test_configure_persists_name_and_panel_owned_fields(hass):
    from tests.test_richmat_family_flow import configure, entry_for

    entry = entry_for(hass, **{const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: "SUTA-B905", const.CONF_HAS_MASSAGE: True, const.CONF_MOTOR_COUNT: 4})
    result = await configure(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BLE_DEVICE_NAME] == "SUTA-B905"
    assert entry.data[const.CONF_HAS_MASSAGE] is False
    assert entry.data[const.CONF_MOTOR_COUNT] == 2


async def test_renewable_timed_motor_uses_declared_native_hold_control(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    started, finish = asyncio.Event(), asyncio.Event()

    async def block_first(_char, packet, **kwargs):
        if packet == codec.text("AT+CTRL=BOTH BACK UP"):
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = block_first
    task = asyncio.create_task(hass.services.async_call(
        const.DOMAIN, "timed_move",
        {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 1000,
         "hold_owner": "card", "hold_generation": 1}, blocking=True,
    ))
    await asyncio.wait_for(started.wait(), 1)
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    finish.set()
    await asyncio.gather(task, stop)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_a_renewed_countdown_is_the_plain_held_gesture(hass, runtime):
    """A renewal request never leases a countdown: it holds it as a finger does."""
    target, client, _ = runtime
    await hass.services.async_call(
        const.DOMAIN, "hold_control",
        {"device_id": "bed", "control": "both_set_tv", "duration": 1,
         "hold_owner": "card", "hold_generation": 2}, blocking=True,
    )
    renewed = written(client)
    assert all(r.kind is not CommandKind.HOLD for r in target._command_scheduler.recent_records)
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN, "hold_control",
        {"device_id": "bed", "control": "both_set_tv", "duration": 30}, blocking=True,
    )
    assert renewed == written(client)


async def test_massage_level_entity_refreshes_on_each_local_zone_change(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    level = next(entity for entity in _number_entities_for(hass, target) if entity.unique_id.endswith("massage_intensity"))
    level.hass = hass
    level.entity_id = "number.suta_level"
    level.async_write_ha_state = MagicMock()
    await level.async_added_to_hass()
    try:
        assert not level.available
        await action(hass, "mass_head_dt", suffix="20")
        assert level.available
        level.async_write_ha_state.assert_called()
        level.async_write_ha_state.reset_mock()
        await action(hass, "massage_off")
        assert not level.available
        assert level.async_write_ha_state.call_count == 2
    finally:
        await level.async_will_remove_from_hass()


@pytest.mark.parametrize("runtime", ["SUTA-B402"], indirect=True)
async def test_lock_switch_sends_lock_and_keeps_the_commanded_state(hass, runtime):
    from custom_components.adjustable_bed.switch import (
        AdjustableBedControllerSwitch,
        _switch_entities_for,
    )

    target, client, _ = runtime
    assert await target.async_connect()
    (lock,) = [e for e in _switch_entities_for(hass, target) if isinstance(e, AdjustableBedControllerSwitch)]
    lock.hass = hass
    lock.entity_id = "switch.suta_lock"
    lock.async_write_ha_state = MagicMock()
    assert lock.assumed_state and lock.is_on is None
    await lock.async_turn_on()
    assert written(client)[-1] == codec.text("AT+SETLOCK=ON")
    assert lock.is_on is True
    await lock.async_turn_off()
    assert written(client)[-1] == codec.text("AT+SETLOCK=OFF")
    assert lock.is_on is False


@pytest.mark.parametrize("runtime", ["SUTA-MOON"], indirect=True)
async def test_automatic_adjustment_shows_the_sent_value_until_the_next_report(hass, runtime):
    from custom_components.adjustable_bed.switch import (
        AdjustableBedControllerSwitch,
        _switch_entities_for,
    )

    target, client, _ = runtime
    assert await target.async_connect()
    left = next(e for e in _switch_entities_for(hass, target)
                if isinstance(e, AdjustableBedControllerSwitch) and e.translation_key == "suta_left_automatic_adjustment")
    left.hass = hass
    left.entity_id = "switch.suta_left_automatic_adjustment"
    left.async_write_ha_state = MagicMock()
    sender, callback = client.start_notify.call_args.args
    # A full-state report: left checked (flag 0), right unchecked.
    full_state = bytearray.fromhex("5359970d000800020a0000020a01000000")
    callback(sender, full_state)
    assert left.is_on is True
    await left.async_turn_off()
    assert written(client)[-1] == codec.binary(0x97, 0x0B, bytes((1, 0)))
    # The bed does not echo the write, so the sent value stands until a new report.
    assert left.is_on is False
    callback(sender, full_state)
    assert left.is_on is True


@pytest.mark.parametrize("runtime", ["SUTA-RBHC", "SUTA-B905"], indirect=True)
async def test_only_rbhc_gets_angle_sensors(hass, runtime):
    from custom_components.adjustable_bed.sensor import (
        AdjustableBedAngleSensor,
        _sensor_entities_for,
    )

    target, _client, _ = runtime
    target._disable_angle_sensing = False
    keys = {e.entity_description.key for e in _sensor_entities_for(hass, target) if isinstance(e, AdjustableBedAngleSensor)}
    assert keys == ({"back_angle", "legs_angle"} if target.capability_controller.name.startswith("SUTA-RBHC") else set())


@pytest.mark.parametrize("runtime", ["SUTA-TEMP"], indirect=True)
async def test_heating_power_on_asks_the_bed_for_both_setpoints(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    sender, callback = client.start_notify.call_args.args
    state = codec.binary(0xA1, 0x85, bytes((25, 33, 26, 28, 6, 6, 0, 0, 0)))
    callback(sender, bytearray(state))
    assert target.controller_state[bed.LEFT_SETPOINT] == 33
    assert target.controller_state[bed.RIGHT_SETPOINT] == 28
    client.write_gatt_char.reset_mock()

    # The power-on acknowledgment carries no setpoint: neither side is known from it.
    callback(sender, bytearray(codec.binary(0xA1, 0x81, b"\x01")))
    assert target.controller_state[bed.LEFT_SETPOINT] is None
    assert target.controller_state[bed.RIGHT_SETPOINT] is None
    await hass.async_block_till_done()
    assert written(client) == [codec.binary(0xA1, 5, b"\x0f")]

    callback(sender, bytearray(codec.binary(0xA1, 0x85, bytes((25, 30, 26, 28, 6, 6, 0, 1, 0)))))
    assert target.controller_state[bed.LEFT_SETPOINT] == 30
    assert target.controller_state[bed.RIGHT_SETPOINT] == 28
    assert target.controller_state[bed.HEATING_ON] is True

    # Turning heating off resets nothing in the app, so nothing is dropped or asked.
    client.write_gatt_char.reset_mock()
    callback(sender, bytearray(codec.binary(0xA1, 0x81, b"\x00")))
    await hass.async_block_till_done()
    assert target.controller_state[bed.LEFT_SETPOINT] == 30 and not written(client)
